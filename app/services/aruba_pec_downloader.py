"""
Aruba PEC Downloader — Download XML Fatture dalla PEC
======================================================

Scarica direttamente dalla casella PEC Aruba (imaps.pec.aruba.it)
gli allegati XML delle fatture elettroniche SDI.

Flusso:
1. Connessione IMAP a imaps.pec.aruba.it
2. Cerca email da mittenti SDI (pec.fatturapa.gov.it, agenziaentrate.gov.it)
3. Scarica allegati .xml e .p7m (fatture firmate digitalmente)
4. Inserisce le fatture nella collezione 'invoices'
5. Evita duplicati via hash del contenuto XML
"""
import imaplib
import email
import os
import hashlib
import re
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from email.header import decode_header
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

# Importa da settings (carica automaticamente /app/backend/.env)
from app.config import settings

# Valori di fallback da .env
PEC_HOST = settings.ARUBA_PEC_HOST
PEC_PORT = settings.ARUBA_PEC_PORT
PEC_USER = settings.ARUBA_PEC_USER or ""
PEC_PASSWORD = settings.ARUBA_PEC_PASSWORD or ""


async def get_pec_credentials(db) -> Dict[str, Any]:
    """
    Legge le credenziali PEC da MongoDB (pec_email_settings).
    Fallback alle variabili d'ambiente se il DB non ha dati.
    """
    try:
        cfg = await db["pec_email_settings"].find_one({}, {"_id": 0})
        if cfg and cfg.get("email") and (cfg.get("app_password") or cfg.get("password")):
            return {
                "host": cfg.get("imap_server", cfg.get("host", PEC_HOST)),
                "port": int(cfg.get("imap_port", cfg.get("port", PEC_PORT))),
                "user": cfg["email"],
                "password": cfg.get("app_password") or cfg.get("password"),
                "source": "database",
            }
    except Exception as e:
        logger.warning(f"Impossibile leggere credenziali PEC da DB: {e}")

    # Fallback a .env
    return {
        "host": PEC_HOST,
        "port": PEC_PORT,
        "user": PEC_USER,
        "password": PEC_PASSWORD,
        "source": "env",
    }

# Mittenti SDI attesi nella PEC
SDI_SENDERS = [
    "sdi",
    "pec.fatturapa.gov.it",
    "agenziaentrate.gov.it",
    "fatturapa.gov.it",
    "noreply@pec",
]

# Namespace XML FatturaPA
NS = {
    'p': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2',
    'p10': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2',
    'ns': 'http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2',
}

UPLOAD_DIR = "/app/app/uploads/pec_xml"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def decode_mime_header(value: str) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    result = ""
    for part, encoding in parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8", errors="replace")
        else:
            result += str(part)
    return result


def is_sdi_sender(from_addr: str) -> bool:
    """Verifica se il mittente è il Sistema di Interscambio."""
    from_lower = from_addr.lower()
    return any(s in from_lower for s in SDI_SENDERS)


def parse_fatturapa_xml(xml_content: bytes) -> Optional[Dict[str, Any]]:
    """
    Parsa un file XML FatturaPA e estrae i dati principali.
    Supporta FatturaPA v1.2 con namespace variabili e encoding windows-1252/UTF-8.
    """
    try:
        # Rimuovi BOM se presente
        content = xml_content
        if content.startswith(b'\xef\xbb\xbf'):
            content = content[3:]

        # Verifica che sia una fattura elettronica (non metadata SDI)
        if b'FatturaElettronica' not in content and b'fatturaelettronica' not in content.lower():
            return None

        # Gestisci encoding windows-1252 (usato da alcuni software di fatturazione)
        # Normalizza l'XML convertendo l'encoding dichiarato
        try:
            # Tenta UTF-8 prima
            root = ET.fromstring(content)
        except ET.ParseError:
            try:
                # Tenta windows-1252
                decoded = content.decode('windows-1252', errors='replace')
                # Rimuovi la dichiarazione di encoding dall'XML per evitare conflitti
                decoded = re.sub(r'encoding=["\'][\w-]+["\']', 'encoding="UTF-8"', decoded)
                root = ET.fromstring(decoded.encode('utf-8'))
            except Exception:
                return None

        # Trova il namespace dinamicamente
        tag = root.tag
        ns_match = re.match(r'\{(.+?)\}', tag)
        ns_uri = ns_match.group(1) if ns_match else ""
        ns = {'n': ns_uri} if ns_uri else {}

        def _find_in_tree(path_parts):
            """Cerca elemento nel tree con qualsiasi namespace."""
            elements = [root]
            for part in path_parts:
                next_els = []
                for el in elements:
                    # Cerca con namespace specifico
                    if ns_uri:
                        found = el.find(f'{{*}}{part}')
                        if found is None:
                            found = el.find(f'{{*}}{part}')
                    else:
                        found = el.find(part)
                    if found is not None:
                        next_els.append(found)
                    # Cerca anche nei figli diretti di tutti gli elementi
                    for child in el:
                        if child.tag.split('}')[-1] == part or child.tag == part:
                            next_els.append(child)
                elements = next_els[:1]  # Prendi solo il primo match
            return elements[0] if elements else None

        def findtext_any(path, default=''):
            """Trova testo con qualsiasi namespace prefix."""
            parts = path.split('/')
            el = _find_in_tree(parts)
            return (el.text or '').strip() if el is not None else default

        def findall_any(path):
            """Trova tutti gli elementi con qualsiasi namespace prefix."""
            parts = path.split('/')
            # Usa iterall per trovare in tutto l'albero
            tag_name = parts[-1]
            return [el for el in root.iter() if el.tag.split('}')[-1] == tag_name]

        # Estrai dati con ricerca per nome tag (ignora namespace)
        def get_by_tag(tag_name):
            for el in root.iter():
                if el.tag.split('}')[-1] == tag_name:
                    return (el.text or '').strip()
            return ''

        # Cedente (fornitore) - Cerca SOLO dentro CedentePrestatore
        cedente_denominazione = ''
        cedente_piva = ''
        cedente_cf = ''
        cedente_nome = ''
        cedente_cognome = ''

        # Cerca P.IVA, CF, Denominazione e Nome/Cognome del cedente
        for el in root.iter():
            tag = el.tag.split('}')[-1]
            if tag == 'CedentePrestatore':
                for sub in el.iter():
                    stag = sub.tag.split('}')[-1]
                    if stag == 'IdCodice' and not cedente_piva:
                        cedente_piva = (sub.text or '').strip()
                    if stag == 'CodiceFiscale' and not cedente_cf:
                        cedente_cf = (sub.text or '').strip()
                    if stag == 'Denominazione' and not cedente_denominazione:
                        cedente_denominazione = (sub.text or '').strip()
                    if stag == 'Nome' and not cedente_nome:
                        cedente_nome = (sub.text or '').strip()
                    if stag == 'Cognome' and not cedente_cognome:
                        cedente_cognome = (sub.text or '').strip()
                break
        
        # Persona fisica: usa Cognome Nome se Denominazione è vuota
        if not cedente_denominazione and (cedente_nome or cedente_cognome):
            cedente_denominazione = f"{cedente_cognome} {cedente_nome}".strip()

        numero_fattura = get_by_tag('Numero')
        data_str = get_by_tag('Data')
        importo_totale = get_by_tag('ImportoTotaleDocumento')
        divisa = get_by_tag('Divisa') or 'EUR'
        tipo_documento = get_by_tag('TipoDocumento')
        modalita_pagamento = get_by_tag('ModalitaPagamento')
        importo_pagamento = get_by_tag('ImportoPagamento')
        data_scadenza = get_by_tag('DataScadenzaPagamento')
        iban = get_by_tag('IBAN')
        imponibile = get_by_tag('ImponibileImporto')
        imposta = get_by_tag('Imposta')
        aliquota_iva = get_by_tag('AliquotaIVA')

        # Descrizioni righe
        descrizioni = [el.text.strip() for el in root.iter()
                       if el.tag.split('}')[-1] == 'Descrizione' and el.text]

        def to_float(s):
            try:
                return float(str(s).replace(',', '.').strip())
            except Exception:
                return 0.0

        total_amount = to_float(importo_totale) or to_float(importo_pagamento)
        imponibile_float = to_float(imponibile)
        imposta_float = to_float(imposta)

        # Validazione: se non c'è né fornitore né importo, non è una fattura valida
        if not cedente_denominazione and total_amount == 0 and not numero_fattura:
            return None

        metodo_map = {
            'MP01': 'contanti', 'MP02': 'assegno', 'MP03': 'assegno_circolare',
            'MP04': 'contanti', 'MP05': 'bonifico', 'MP06': 'vaglia',
            'MP07': 'bollettino', 'MP08': 'carta', 'MP09': 'rid',
            'MP10': 'rid', 'MP11': 'rid', 'MP12': 'rid',
            'MP13': 'rid', 'MP14': 'quiesecentpostale', 'MP15': 'carta',
            'MP16': 'domiciliazione', 'MP17': 'domiciliazione', 'MP18': 'bollettino',
            'MP19': 'sepa', 'MP20': 'sepa', 'MP21': 'sepa', 'MP22': 'sepa',
        }
        metodo_pagamento = metodo_map.get(modalita_pagamento, 'bonifico')

        return {
            "supplier_name": cedente_denominazione or "Fornitore Sconosciuto",
            "supplier_vat": cedente_piva,
            "supplier_cf": cedente_cf,
            "invoice_number": numero_fattura,
            "invoice_date": data_str,
            "due_date": data_scadenza,
            "total_amount": total_amount,
            "taxable_amount": imponibile_float,
            "vat_amount": imposta_float,
            "vat_rate": to_float(aliquota_iva),
            "currency": divisa,
            "document_type": tipo_documento,
            "payment_method_code": modalita_pagamento,
            "payment_method": metodo_pagamento,
            "iban": iban,
            "descrizione": '; '.join(descrizioni[:3]) if descrizioni else "",
            "fonte": "aruba_pec",
        }

    except Exception as e:
        logger.error(f"Errore parse XML FatturaPA: {e}")
        return None


def _decode_p7m_openssl(payload: bytes) -> Optional[bytes]:
    """
    Decodifica un file P7M (PKCS#7/CMS signed) usando OpenSSL via subprocess.
    Restituisce il contenuto XML decodificato o None se fallisce.
    """
    import subprocess
    import tempfile

    try:
        # Scrivi il payload in un file temporaneo
        with tempfile.NamedTemporaryFile(suffix='.p7m', delete=False) as tmp_in:
            tmp_in.write(payload)
            tmp_in_path = tmp_in.name

        # Prova formato DER (più comune per fatture italiane)
        for fmt in ['DER', 'PEM']:
            try:
                result = subprocess.run(
                    ['openssl', 'cms', '-verify', '-noverify', '-inform', fmt, '-in', tmp_in_path],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0 and result.stdout and len(result.stdout) > 100:
                    logger.info(f"[PEC] P7M decodificato con OpenSSL (formato {fmt})")
                    return result.stdout
            except subprocess.TimeoutExpired:
                continue

            # Prova anche con smime (vecchio formato)
            try:
                result = subprocess.run(
                    ['openssl', 'smime', '-verify', '-noverify', '-inform', fmt, '-in', tmp_in_path],
                    capture_output=True, timeout=10
                )
                if result.returncode == 0 and result.stdout and len(result.stdout) > 100:
                    logger.info(f"[PEC] P7M decodificato con OpenSSL smime (formato {fmt})")
                    return result.stdout
            except subprocess.TimeoutExpired:
                continue

    except Exception as e:
        logger.debug(f"[PEC] OpenSSL P7M decode fallito: {e}")
    finally:
        try:
            os.unlink(tmp_in_path)
        except Exception:
            pass

    return None


def _decode_p7m_asn1(payload: bytes) -> Optional[bytes]:
    """
    Decodifica un file P7M usando asn1crypto per estrarre il contenuto firmato.
    Gestisce sia SignedData che EnvelopedData.
    """
    try:
        from asn1crypto import cms

        content_info = cms.ContentInfo.load(payload)
        content_type = content_info['content_type'].native

        if content_type == 'signed_data':
            signed_data = content_info['content']
            encap_content = signed_data['encap_content_info']
            content_bytes = encap_content['content'].native
            if content_bytes and len(content_bytes) > 100:
                logger.info("[PEC] P7M decodificato con asn1crypto (signed_data)")
                return content_bytes

        elif content_type == 'enveloped_data':
            logger.warning("[PEC] P7M con EnvelopedData (crittografato) — non supportato senza chiave privata")
            return None

    except Exception as e:
        logger.debug(f"[PEC] asn1crypto P7M decode fallito: {e}")

    return None


def _extract_xml_from_bytes(payload: bytes, filename: str) -> Optional[bytes]:
    """
    Cerca marcatori XML FatturaElettronica nel payload grezzo (fallback).
    """
    xml_start = payload.find(b'<?xml')
    if xml_start == -1:
        for marker in [b'<p:FatturaElettronica', b'<FatturaElettronica',
                       b'<ns2:FatturaElettronica', b'<ns3:FatturaElettronica',
                       b'<P:FatturaElettronica']:
            idx = payload.find(marker)
            if idx >= 0:
                xml_start = idx
                break
    if xml_start == -1:
        return None

    xml_content = payload[xml_start:]
    for end_marker in [b'</p:FatturaElettronica>', b'</FatturaElettronica>',
                       b'</ns2:FatturaElettronica>', b'</ns3:FatturaElettronica>',
                       b'</P:FatturaElettronica>']:
        idx_end = xml_content.rfind(end_marker)
        if idx_end >= 0:
            xml_content = xml_content[:idx_end + len(end_marker)]
            break

    return xml_content


def _decode_p7m(payload: bytes, filename: str) -> Optional[bytes]:
    """
    Decodifica P7M con 3 metodi in cascata:
    1. OpenSSL (più affidabile per CAdES/CMS)
    2. asn1crypto (puro Python, senza binari esterni)
    3. Ricerca byte grezza (fallback per P7M semplici)
    """
    # Metodo 1: OpenSSL
    result = _decode_p7m_openssl(payload)
    if result:
        return result

    # Metodo 2: asn1crypto
    result = _decode_p7m_asn1(payload)
    if result:
        return result

    # Metodo 3: ricerca marcatori XML nel payload grezzo
    result = _extract_xml_from_bytes(payload, filename)
    if result:
        logger.info(f"[PEC] P7M decodificato con ricerca byte: {filename}")
        return result

    logger.warning(f"[PEC] P7M non decodificabile con nessun metodo: {filename}")
    return None


def _pec_extract_xml_from_part(part, fname_lower: str, filename: str) -> Optional[bytes]:
    """
    Estrae il contenuto XML (grezzo o da .p7m) da una singola parte MIME.
    Restituisce None se il file va saltato.
    Supporta P7M firmati digitalmente (CAdES) con decodifica completa.
    """
    content_type = part.get_content_type()

    # Accetta .xml e .p7m (firma CAdES)
    is_xml = (
        fname_lower.endswith('.xml') or
        fname_lower.endswith('.p7m') or
        fname_lower.endswith('.xml.p7m') or
        content_type in ('application/xml', 'text/xml', 'application/pkcs7-mime')
    )
    if not is_xml:
        return None

    # Salta file di metadati PEC (non fatture)
    if (fname_lower.endswith('_mt_001.xml') or
            fname_lower in ('daticert.xml', 'smime.p7s', 'postacert.eml')):
        return None

    payload = part.get_payload(decode=True)
    if not payload or len(payload) < 200:
        return None

    xml_content = payload

    if fname_lower.endswith('.p7m'):
        # Decodifica P7M con metodi multipli (OpenSSL → asn1crypto → byte search)
        decoded = _decode_p7m(payload, filename)
        if decoded is None:
            return None
        xml_content = decoded

    return xml_content


def _pec_fetch_xml_sync(
    host: str, port: int, user: str, password: str, since_days: int = 90
) -> List[Dict[str, Any]]:
    """
    Funzione SINCRONA pura per IMAP — gira in asyncio.to_thread().
    NON contiene chiamate async, NON tocca MongoDB.
    Scansiona sia INBOX che INBOX.lette (email già lette) per le fatture SDI.
    Restituisce lista di dict con i dati grezzi degli allegati XML/P7M trovati.
    """
    results = []
    since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")

    # Cartelle da scansionare: INBOX (posta nuova) + INBOX.lette (già lette)
    FOLDERS_TO_SCAN = ["INBOX", "INBOX.lette"]

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, password)

        seen_eids: set = set()  # evita doppi ID se stesso messaggio in due cartelle

        for folder in FOLDERS_TO_SCAN:
            try:
                status, _ = mail.select(folder)
                if status != "OK":
                    logger.debug(f"[PEC] Cartella non accessibile: {folder}")
                    continue

                _, messages = mail.search(None, f'SINCE {since_date}')
                email_ids = messages[0].split() if messages[0] else []
                logger.info(f"[PEC] {len(email_ids)} email in {folder} dal {since_date}")

                for eid in email_ids:
                    eid_str = eid.decode() if isinstance(eid, bytes) else str(eid)
                    folder_key = f"{folder}:{eid_str}"
                    if folder_key in seen_eids:
                        continue
                    seen_eids.add(folder_key)

                    try:
                        _, msg_data = mail.fetch(eid, "(RFC822)")
                        if not msg_data or not msg_data[0]:
                            continue
                        msg = email.message_from_bytes(msg_data[0][1])

                        from_addr = decode_mime_header(msg.get("From", ""))
                        subject   = decode_mime_header(msg.get("Subject", ""))

                        for part in msg.walk():
                            filename = decode_mime_header(part.get_filename() or "")
                            if not filename:
                                continue
                            fname_lower = filename.lower()

                            xml_content = _pec_extract_xml_from_part(part, fname_lower, filename)
                            if xml_content is None:
                                continue

                            results.append({
                                "filename":    filename,
                                "xml_content": xml_content,
                                "from_addr":   from_addr,
                                "subject":     subject,
                                "eid":         eid_str,
                                "folder":      folder,
                            })

                    except Exception as e:
                        logger.error(f"[PEC] Errore email {eid} in {folder}: {e}")

                mail.close()

            except Exception as e:
                logger.warning(f"[PEC] Errore cartella {folder}: {e}")

        mail.logout()

    except imaplib.IMAP4.error as e:
        logger.error(f"[PEC] Errore autenticazione IMAP: {e}")
    except Exception as e:
        logger.error(f"[PEC] Errore connessione: {e}")

    logger.info(f"[PEC] Totale XML trovati in tutte le cartelle: {len(results)}")
    return results


async def download_pec_invoices(
    db,
    since_days: int = 30,
    host: str = None,
    port: int = None,
    user: str = None,
    password: str = None
) -> Dict[str, Any]:
    """
    Scarica e processa le fatture XML dalla PEC Aruba — NON bloccante.
    La parte IMAP gira in asyncio.to_thread(); MongoDB è gestito async.
    """
    creds = await get_pec_credentials(db)
    _host     = host     or creds["host"]
    _port     = port     or creds["port"]
    _user     = user     or creds["user"]
    _password = password or creds["password"]

    stats = {
        "emails_checked": 0,
        "xml_found": 0,
        "new_invoices": 0,
        "duplicates_skipped": 0,
        "errors": 0,
        "inserted": [],
        "credentials_source": creds.get("source", "unknown"),
    }

    if not _user or not _password:
        return {"success": False, "error": "Credenziali PEC non configurate", "stats": stats}

    # ── IMAP in thread separato (NON blocca l'event loop) ──────────────────
    logger.info(f"[PEC] Avvio download {_user} (ultimi {since_days} giorni)")
    raw_items = await asyncio.to_thread(
        _pec_fetch_xml_sync, _host, _port, _user, _password, since_days
    )
    stats["xml_found"] = len(raw_items)
    logger.info(f"[PEC] XML trovati: {len(raw_items)}")

    # ── Elaborazione async (MongoDB) ────────────────────────────────────────
    for item in raw_items:
        try:
            xml_content  = item["xml_content"]
            filename     = item["filename"]
            from_addr    = item["from_addr"]
            subject      = item["subject"]

            content_hash = hashlib.md5(xml_content).hexdigest()

            existing = await db["invoices"].find_one(
                {"xml_hash": content_hash}, {"_id": 0, "id": 1}
            )
            if existing:
                stats["duplicates_skipped"] += 1
                continue

            invoice_data = parse_fatturapa_xml(xml_content)
            if not invoice_data:
                logger.warning(f"[PEC] XML non parsabile: {filename}")
                stats["errors"] += 1
                continue

            # Salva file XML su disco
            safe_name = re.sub(r'[^\w\-_.]', '_', filename) or f"fattura_{content_hash[:8]}.xml"
            file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex[:8]}_{safe_name}")
            with open(file_path, 'wb') as f:
                f.write(xml_content)

            anno = (
                int(invoice_data["invoice_date"][:4])
                if invoice_data.get("invoice_date") and len(invoice_data["invoice_date"]) >= 4
                else datetime.now().year
            )

            invoice_doc = {
                "id": str(uuid.uuid4()),
                "xml_hash": content_hash,
                "xml_filename": filename,
                "xml_file_path": file_path,
                "supplier_name": invoice_data["supplier_name"],
                "cedente_denominazione": invoice_data["supplier_name"],
                "supplier_vat": invoice_data["supplier_vat"],
                "supplier_cf": invoice_data["supplier_cf"],
                "invoice_number": invoice_data["invoice_number"],
                "invoice_date": invoice_data["invoice_date"],
                "due_date": invoice_data["due_date"],
                "total_amount": invoice_data["total_amount"],
                "taxable_amount": invoice_data["taxable_amount"],
                "vat_amount": invoice_data["vat_amount"],
                "vat_rate": invoice_data["vat_rate"],
                "currency": invoice_data["currency"],
                "document_type": invoice_data["document_type"],
                "payment_method": invoice_data["payment_method"],
                "payment_method_code": invoice_data["payment_method_code"],
                "iban": invoice_data["iban"],
                "descrizione": invoice_data["descrizione"],
                "stato": "importata",
                "fonte": "aruba_pec",
                "email_from": from_addr,
                "email_subject": subject,
                "pec_email_id": item["eid"],
                "imported_at": datetime.now(timezone.utc).isoformat(),
                "anno": anno,
            }

            await db["invoices"].insert_one(invoice_doc)
            stats["new_invoices"] += 1
            stats["inserted"].append({
                "fornitore": invoice_data["supplier_name"],
                "numero": invoice_data["invoice_number"],
                "data": invoice_data["invoice_date"],
                "importo": invoice_data["total_amount"],
            })
            logger.info(f"[PEC] Fattura importata: {invoice_data['supplier_name']} | {invoice_data['invoice_number']} | €{invoice_data['total_amount']}")

            # --- EVENT BUS: propaga evento fattura creata (import PEC) ---
            # Fondamentale: questo è il flusso principale di ingresso fatture del
            # gestionale (scheduler orario). Senza questo, le fatture PEC
            # saltavano completamente il sistema relazionale.
            try:
                from app.services.event_bus import propagate_event, EventTypes
                await propagate_event(EventTypes.FATTURA_CREATED, {
                    "fattura_id": invoice_doc["id"],
                    "numero_documento": invoice_data.get("invoice_number", ""),
                    "tipo_documento": invoice_data.get("document_type", "TD01"),
                    "importo_totale": invoice_data.get("total_amount", 0),
                    "fornitore_id": None,  # flusso PEC non linka fornitore, handler lo gestisce
                    "fornitore_ragione_sociale": invoice_data.get("supplier_name", ""),
                    "fornitore_piva": invoice_data.get("supplier_vat", ""),
                    "fornitore_nuovo": True,  # handler alert_fornitore farà il check reale
                    "fornitore_iban": invoice_data.get("iban"),
                    "metodo_pagamento": invoice_data.get("payment_method") or "",
                    "data_documento": invoice_data.get("invoice_date", ""),
                    "data_scadenza": invoice_data.get("due_date"),
                    "stato": "importata",
                    "pagato": False,
                }, db, source_module="aruba_pec_downloader")
            except Exception:
                logger.exception("Errore propagazione evento fattura.created (PEC)")

        except Exception as e:
            logger.error(f"[PEC] Errore elaborazione {item.get('filename','?')}: {e}")
            stats["errors"] += 1

    logger.info(f"[PEC] Completato: {stats['new_invoices']} nuove, {stats['duplicates_skipped']} duplicati")
    return {"success": True, "stats": stats}


async def test_pec_connection(db=None, host: str = None, port: int = None, user: str = None, password: str = None) -> Dict[str, Any]:
    """Test rapido della connessione PEC. Legge credenziali da MongoDB se db è fornito."""
    if db is not None:
        creds = await get_pec_credentials(db)
        _host = host or creds["host"]
        _port = port or creds["port"]
        _user = user or creds["user"]
        _password = password or creds["password"]
    else:
        _host = host or PEC_HOST
        _port = port or PEC_PORT
        _user = user or PEC_USER
        _password = password or PEC_PASSWORD

    if not _user or not _password:
        return {"success": False, "error": "Credenziali PEC non configurate"}

    try:
        mail = imaplib.IMAP4_SSL(_host, _port)
        mail.login(_user, _password)
        mail.select("INBOX")
        _, messages = mail.search(None, 'ALL')
        total = len(messages[0].split()) if messages[0] else 0
        mail.logout()
        return {
            "success": True,
            "message": f"Connessione PEC riuscita! Casella: {_user} | Email totali: {total}",
            "host": _host,
            "user": _user,
            "total_emails": total
        }
    except imaplib.IMAP4.error as e:
        return {"success": False, "error": f"Autenticazione fallita: {e}", "host": _host, "user": _user}
    except Exception as e:
        return {"success": False, "error": str(e), "host": _host, "user": _user}
